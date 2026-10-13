#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>
#include "NvmCardReader.h"

const char* WIFI_SSID="CHANGE_ME";
const char* WIFI_PASSWORD="CHANGE_ME";
// Replace with the server LAN IP; default API port is 8011. Do not add a trailing slash.
const char* NVM_BASE_URL="http://192.168.1.10:8011";
const char* DEVICE_ID="vm-01";
const char* NVM_DEVICE_KEY="CHANGE_DEVICE_KEY";

#define I2C_SDA 8
#define I2C_SCL 9
#define PN532_IRQ 7
#define PN532_RESET 10
#define RC522_SCK 12
#define RC522_MISO 13
#define RC522_MOSI 11
#define RC522_SS 14
#define RC522_RST 15
#define BUTTON_UP 4
#define BUTTON_DOWN 5
#define BUTTON_SELECT 6
#define SERVO_COUNT 5
// IR break-beam output across the shared product chute. Confirm polarity for the chosen module.
#define PRODUCT_DROP_SENSOR_PIN 1
#define PRODUCT_SENSOR_BLOCKED_LEVEL HIGH
#define PRODUCT_DROP_TIMEOUT_MS 4000UL
const int SERVO_PINS[SERVO_COUNT]={3,16,17,18,21};
#define OLED_ADDR 0x3C

NvmCardReader card(PN532_IRQ,PN532_RESET,RC522_SCK,RC522_MISO,RC522_MOSI,RC522_SS,RC522_RST);
Adafruit_SSD1306 display(128,64,&Wire,-1);
Servo dispensers[SERVO_COUNT];
Preferences vendingPrefs;
unsigned long lastHeartbeat=0,lastCatalogRefresh=0,vendingSequence=0;
bool readerReady=false,displayReady=false,pendingDispenseReport=false,pendingDispenseSuccess=true;
String pendingDispenseTx="";
int selectedIndex=0,productCount=0;
bool pendingTransaction=false;
String pendingTransactionId="",pendingTransactionPhase="";
int pendingServoChannel=0;
// Persist the complete create request before sending it. If the HTTP response is lost,
// retry the identical idempotency key instead of starting a new vend.
bool pendingCreateRequest=false;
String pendingCreateProduct="",pendingCreateCredential="";
unsigned long pendingCreateSequence=0;
int pendingCreateServo=0;
bool createRequestRejected=false;

struct Product{String id,name;long price;int stock;bool enabled;int servo_channel;};
Product productsList[16];

String request(const String& method,const String& path,const String& body,int& code){
  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(8000);
  http.begin(String(NVM_BASE_URL)+path);
  http.addHeader("Content-Type","application/json");
  http.addHeader("X-NVM-Device-Key",NVM_DEVICE_KEY);
  if(method=="GET")code=http.GET();else if(method=="POST")code=http.POST(body);else code=-1;
  String out=code>0?http.getString():"";http.end();return out;
}
String jsonString(const String& json,const String& key){
  String m="\""+key+"\":\"";int p=json.indexOf(m);if(p<0)return "";p+=m.length();int e=json.indexOf('"',p);return e<0?"":json.substring(p,e);
}
long jsonLong(const String& json,const String& key){
  String m="\""+key+"\":";int p=json.indexOf(m);if(p<0)return -1;p+=m.length();while(p<(int)json.length()&&json[p]==' ')p++;int e=p;while(e<(int)json.length()&&isDigit(json[e]))e++;return json.substring(p,e).toInt();
}
void showMessage(const String&a,const String&b="",const String&c=""){
  if(!displayReady){Serial.printf("DISPLAY: %s | %s | %s\n",a.c_str(),b.c_str(),c.c_str());return;}
  display.clearDisplay();display.setTextSize(1);display.setTextColor(SSD1306_WHITE);display.setCursor(0,0);
  display.println(a);if(b.length())display.println(b);if(c.length())display.println(c);display.display();
}
void heartbeat(){
  if(WiFi.status()!=WL_CONNECTED){Serial.println("HEARTBEAT skipped: WiFi offline");return;}
  int code=0;String body="{\"device_type\":\"esp32-s3-vending\",\"status\":\"active\"}";
  String reply=request("POST",String("/api/v1/devices/")+DEVICE_ID+"/heartbeat",body,code);
  Serial.printf("HEARTBEAT %d %s\n",code,reply.c_str());
}
bool connectWifi(unsigned long timeoutMs=10000){
  WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);Serial.print("WiFi");
  unsigned long started=millis();
  while(WiFi.status()!=WL_CONNECTED && millis()-started<timeoutMs){delay(250);Serial.print(".");}
  if(WiFi.status()!=WL_CONNECTED){Serial.println("\nWiFi unavailable; retry later");return false;}
  Serial.printf("\nIP %s\n",WiFi.localIP().toString().c_str());
  return true;
}
void parseProducts(const String&json){
  productCount=0;int pos=0;
  while(productCount<16){
    const String productPrefix="\"product_id\":\"";
    int p=json.indexOf(productPrefix,pos);if(p<0)break;int s=p+productPrefix.length(),e=json.indexOf('"',s);if(e<0)break;
    Product&x=productsList[productCount];x.id=json.substring(s,e);
    const String namePrefix="\"name\":\"";
    int n=json.indexOf(namePrefix,e),ns=n<0?-1:n+namePrefix.length(),ne=ns<0?-1:json.indexOf('"',ns);x.name=(ns>=0&&ne>=0)?json.substring(ns,ne):x.id;
    int q=json.indexOf("\"effective_price\":",e);String priceKey="effective_price";if(q<0){q=json.indexOf("\"price\":",e);priceKey="price";}x.price=q>=0?jsonLong(json.substring(q),priceKey):0;
    q=json.indexOf("\"stock\":",e);x.stock=q>=0?jsonLong(json.substring(q),"stock"):0;
    q=json.indexOf("\"enabled\":",e);x.enabled=q>=0&&json.substring(q,q+20).indexOf("true")>=0;
    q=json.indexOf("\"servo_channel\":",e);x.servo_channel=q>=0?jsonLong(json.substring(q),"servo_channel"):productCount+1;
    if(x.servo_channel<1||x.servo_channel>SERVO_COUNT)x.servo_channel=productCount+1;
    pos=e+1;productCount++;
  }
}
void clearPendingCreateRequest(){
  vendingPrefs.putBool("create_pending",false);
  vendingPrefs.remove("create_product");vendingPrefs.remove("create_credential");
  vendingPrefs.remove("create_seq");vendingPrefs.remove("create_servo");
  pendingCreateRequest=false;pendingCreateProduct="";pendingCreateCredential="";
  pendingCreateSequence=0;pendingCreateServo=0;
}
void savePendingCreateRequest(const String&product,const String&credential,unsigned long seq,int servoChannel){
  vendingPrefs.putString("create_product",product);
  vendingPrefs.putString("create_credential",credential);
  vendingPrefs.putULong("create_seq",seq);
  vendingPrefs.putInt("create_servo",servoChannel);
  vendingPrefs.putBool("create_pending",true);
  pendingCreateRequest=true;pendingCreateProduct=product;pendingCreateCredential=credential;
  pendingCreateSequence=seq;pendingCreateServo=servoChannel;
}
void clearPendingTransaction(){
  vendingPrefs.putBool("tx_pending",false);vendingPrefs.remove("tx_id");vendingPrefs.remove("tx_phase");vendingPrefs.remove("tx_servo");
  pendingTransaction=false;pendingTransactionId="";pendingTransactionPhase="";pendingServoChannel=0;
}
void savePendingTransaction(const String&tx,const String&phase,int servoChannel){
  vendingPrefs.putString("tx_id",tx);vendingPrefs.putString("tx_phase",phase);vendingPrefs.putInt("tx_servo",servoChannel);vendingPrefs.putBool("tx_pending",true);
  pendingTransaction=true;pendingTransactionId=tx;pendingTransactionPhase=phase;pendingServoChannel=servoChannel;
}
bool products(){
  int code=0;String reply=request("GET",String("/api/v1/vending/")+DEVICE_ID+"/products","",code);
  Serial.printf("PRODUCTS %d %s\n",code,reply.c_str());
  if(code<200||code>=300){showMessage("SERVER ERROR","Products unavailable");return false;}
  parseProducts(reply);if(!productCount){showMessage("NVM VENDING","No products");return false;}
  if(selectedIndex>=productCount)selectedIndex=0;Product&x=productsList[selectedIndex];
  showMessage("SELECT PRODUCT",x.name,"Rp "+String(x.price));return true;
}
String beginTransaction(const String&product,const String&credential,const String&seq){
  createRequestRejected=false;
  String body="{\"product_id\":\""+product+"\",\"credential_id\":\""+credential+"\",\"idempotency_key\":\""+String(DEVICE_ID)+":"+seq+"\"}";
  String path=String("/api/v1/vending/")+DEVICE_ID+"/transactions";
  for(int attempt=1;attempt<=2;attempt++){
    if(WiFi.status()!=WL_CONNECTED && !connectWifi(3000))continue;
    int code=0;String reply=request("POST",path,body,code);
    String tx=jsonString(reply,"transaction_id");
    Serial.printf("BEGIN attempt=%d code=%d %s\n",attempt,code,reply.c_str());
    if(tx.length())return tx;
    if(code>=400 && code<500){createRequestRejected=true;return "";}
    delay(250);
  }
  return "";
}
bool authorize(const String&tx){
  int code=0;String reply=request("POST","/api/v1/vending/transactions/"+tx+"/authorize","",code);
  Serial.printf("AUTHORIZE %d %s\n",code,reply.c_str());return code>=200&&code<300;
}
void savePendingDispense(const String&tx,bool success){
  vendingPrefs.putString("disp_tx",tx);
  vendingPrefs.putBool("disp_success",success);
  vendingPrefs.putBool("disp_pending",true);
  pendingDispenseTx=tx;pendingDispenseSuccess=success;pendingDispenseReport=true;
}
void clearPendingDispense(){
  vendingPrefs.putBool("disp_pending",false);
  vendingPrefs.remove("disp_tx");vendingPrefs.remove("disp_success");
  pendingDispenseTx="";pendingDispenseReport=false;pendingDispenseSuccess=true;
}
bool reportDispense(const String&tx,bool success){
  String body=success?"{\"success\":true}":"{\"success\":false}";
  for(int attempt=1;attempt<=3;attempt++){
    if(WiFi.status()!=WL_CONNECTED && !connectWifi(3000))continue;
    int code=0;String reply=request("POST","/api/v1/vending/transactions/"+tx+"/dispense",body,code);
    Serial.printf("DISPENSE REPORT attempt=%d code=%d %s\n",attempt,code,reply.c_str());
    if(code>=200&&code<300){clearPendingDispense();if(pendingTransaction&&pendingTransactionId==tx)clearPendingTransaction();return true;}
    if(code>0&&code<500)break;
    delay(300);
  }
  return false;
}
bool actuateAndDetectProduct(Servo&servo){
  // A blocked beam before vending indicates an obstruction or sensor fault.
  if(digitalRead(PRODUCT_DROP_SENSOR_PIN)==PRODUCT_SENSOR_BLOCKED_LEVEL){
    Serial.println("IR DROP SENSOR: beam blocked before dispense; refusing actuation");
    return false;
  }
  const unsigned long started=millis();
  bool servoReturned=false,seenBlocked=false;
  servo.write(70);
  while(millis()-started<PRODUCT_DROP_TIMEOUT_MS){
    const unsigned long elapsed=millis()-started;
    if(!servoReturned && elapsed>=700UL){servo.write(10);servoReturned=true;}
    const bool blocked=digitalRead(PRODUCT_DROP_SENSOR_PIN)==PRODUCT_SENSOR_BLOCKED_LEVEL;
    if(blocked)seenBlocked=true;
    // Require a complete blocked-then-clear passage, not just an interrupted beam.
    if(seenBlocked && !blocked){
      if(!servoReturned)servo.write(10);
      Serial.println("IR DROP SENSOR: product passage confirmed");
      return true;
    }
    delay(2);
  }
  if(!servoReturned)servo.write(10);
  Serial.println("IR DROP SENSOR: no complete product passage detected");
  return false;
}
bool dispense(const String&tx,int servoChannel){
  if(servoChannel<1||servoChannel>SERVO_COUNT){
    savePendingDispense(tx,false);
    reportDispense(tx,false);
    return false;
  }
  Servo&servo=dispensers[servoChannel-1];
  const bool detected=actuateAndDetectProduct(servo);
  // Persist the sensor result before reporting it. Recovery retries only the
  // server report; it never repeats a potentially completed physical vend.
  savePendingDispense(tx,detected);
  if(!reportDispense(tx,detected))return false;
  return detected;
}
void scanCard(){
  if(!readerReady||!productCount)return;Product&x=productsList[selectedIndex];if(!x.enabled||x.stock<=0)return;
  uint8_t uid[NVM_MAX_UID_LENGTH]={0},len=0;if(!card.readUID(uid,len))return;
  String credential="nfc-";for(uint8_t i=0;i<len;i++){if(uid[i]<16)credential+="0";credential+=String(uid[i],HEX);}credential.toLowerCase();
  showMessage("CARD DETECTED",credential,"Checking...");
  ++vendingSequence;vendingPrefs.putULong("tx_seq",vendingSequence);
  savePendingCreateRequest(x.id,credential,vendingSequence,x.servo_channel);
  String tx=beginTransaction(pendingCreateProduct,pendingCreateCredential,String(pendingCreateSequence));
  if(!tx.length()){
    if(createRequestRejected){clearPendingCreateRequest();showMessage("TRANSACTION REJECTED","Check stock/card");}
    else showMessage("CREATE PENDING","Retry same request");
    delay(1200);return;
  }
  clearPendingCreateRequest();
  savePendingTransaction(tx,"created",x.servo_channel);
  if(!authorize(tx)){showMessage("PAYMENT PENDING","Checking status");delay(800);return;}
  savePendingTransaction(tx,"authorized",x.servo_channel);
  showMessage("PAYMENT OK",x.name,"Dispensing...");
  savePendingTransaction(tx,"dispensing",x.servo_channel);
  if(dispense(tx,x.servo_channel)){showMessage("TAKE PRODUCT",x.name);delay(800);products();}
  else if(pendingDispenseReport)showMessage("RESULT PENDING","Retry server report");
  else showMessage("DISPENSE ERROR","Refund recorded");
  delay(1000);
}
void setup(){
  Serial.begin(115200);delay(300);
  vendingPrefs.begin("nvm-vend",false);
  vendingSequence=vendingPrefs.getULong("tx_seq",0);
  pendingTransaction=vendingPrefs.getBool("tx_pending",false);
  if(pendingTransaction){pendingTransactionId=vendingPrefs.getString("tx_id","");pendingTransactionPhase=vendingPrefs.getString("tx_phase","created");pendingServoChannel=vendingPrefs.getInt("tx_servo",0);if(!pendingTransactionId.length()||pendingServoChannel<1||pendingServoChannel>SERVO_COUNT){Serial.println("FATAL: pending transaction metadata invalid");while(true)delay(1000);}}
  pendingCreateRequest=vendingPrefs.getBool("create_pending",false);
  if(pendingCreateRequest){
    pendingCreateProduct=vendingPrefs.getString("create_product","");
    pendingCreateCredential=vendingPrefs.getString("create_credential","");
    pendingCreateSequence=vendingPrefs.getULong("create_seq",0);
    pendingCreateServo=vendingPrefs.getInt("create_servo",0);
    if(!pendingCreateProduct.length()||!pendingCreateCredential.length()||pendingCreateSequence==0||pendingCreateServo<1||pendingCreateServo>SERVO_COUNT){Serial.println("FATAL: pending create request metadata invalid");while(true)delay(1000);}
  }
  pendingDispenseReport=vendingPrefs.getBool("disp_pending",false);
  if(pendingDispenseReport){
    pendingDispenseTx=vendingPrefs.getString("disp_tx","");
    pendingDispenseSuccess=vendingPrefs.getBool("disp_success",true);
    if(!pendingDispenseTx.length()){Serial.println("FATAL: pending dispense transaction ID missing");while(true)delay(1000);}
  }
  pinMode(BUTTON_UP,INPUT_PULLUP);pinMode(BUTTON_DOWN,INPUT_PULLUP);pinMode(BUTTON_SELECT,INPUT_PULLUP);
  pinMode(PRODUCT_DROP_SENSOR_PIN,INPUT_PULLUP);
  Wire.begin(I2C_SDA,I2C_SCL);displayReady=display.begin(SSD1306_SWITCHCAPVCC,OLED_ADDR);
  for(int i=0;i<SERVO_COUNT;i++){dispensers[i].setPeriodHertz(50);dispensers[i].attach(SERVO_PINS[i],500,2400);dispensers[i].write(10);}
  showMessage("NVM VENDING","Starting...");
  if(connectWifi()){heartbeat();products();}
  readerReady=card.begin(I2C_SDA,I2C_SCL);
}
void loop(){
  if(WiFi.status()!=WL_CONNECTED){showMessage("SERVER ERROR","WiFi disconnected");connectWifi(3000);delay(100);return;}
  if(pendingDispenseReport){
    showMessage("RESULT PENDING","Retry server report");
    reportDispense(pendingDispenseTx,pendingDispenseSuccess);
    delay(250);return;
  }
  if(pendingCreateRequest){
    showMessage("CREATE PENDING","Retry same request");
    String tx=beginTransaction(pendingCreateProduct,pendingCreateCredential,String(pendingCreateSequence));
    if(tx.length()){
      const int servoChannel=pendingCreateServo;
      clearPendingCreateRequest();
      savePendingTransaction(tx,"created",servoChannel);
    }else if(createRequestRejected){
      clearPendingCreateRequest();
      showMessage("CREATE REJECTED","Ready to retry");
    }
    delay(500);return;
  }
  if(pendingTransaction){
    int code=0;String status=request("GET","/api/v1/vending/transactions/"+pendingTransactionId,"",code);
    if(code<200||code>=300){showMessage("TX STATUS UNKNOWN","Retrying server");delay(500);return;}
    String state=jsonString(status,"status");
    if(state=="completed"||state=="refunded"||state=="failed"){clearPendingTransaction();showMessage("TX RESOLVED",state);delay(500);return;}
    if(state=="refunding"){reportDispense(pendingTransactionId,false);showMessage("REFUND RECOVERY","Checking server");delay(500);return;}
    if(state=="pending"){
      if(!authorize(pendingTransactionId)){showMessage("PAYMENT PENDING","Retry status");delay(500);return;}
      savePendingTransaction(pendingTransactionId,"authorized",pendingServoChannel);state="authorized";
    }
    if(state=="authorized"){
      if(pendingTransactionPhase=="dispensing"){
        savePendingDispense(pendingTransactionId,false);reportDispense(pendingTransactionId,false);
        showMessage("DISPENSE UNCERTAIN","Refund requested");delay(500);return;
      }
      savePendingTransaction(pendingTransactionId,"dispensing",pendingServoChannel);
      bool ok=dispense(pendingTransactionId,pendingServoChannel);
      if(ok){showMessage("TAKE PRODUCT");products();}else if(pendingDispenseReport)showMessage("RESULT PENDING","Retry server report");
      delay(500);return;
    }
    showMessage("TX NEEDS REVIEW",state);delay(500);return;
  }
  if(millis()-lastHeartbeat>=30000UL){lastHeartbeat=millis();heartbeat();}
  if(millis()-lastCatalogRefresh>=60000UL){lastCatalogRefresh=millis();products();}
  if(digitalRead(BUTTON_UP)==LOW){if(productCount)selectedIndex=(selectedIndex+productCount-1)%productCount;products();delay(250);}
  if(digitalRead(BUTTON_DOWN)==LOW){if(productCount)selectedIndex=(selectedIndex+1)%productCount;products();delay(250);}
  if(digitalRead(BUTTON_SELECT)==LOW){showMessage("READY",productCount?productsList[selectedIndex].name:"No product","Tap NFC card");delay(250);}
  scanCard();
  if(Serial.available()){String line=Serial.readStringUntil('\n');line.trim();if(line=="PRODUCTS")products();}
}
