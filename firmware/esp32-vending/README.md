# NVM ESP32-S3 Vending

Server is the source of truth for product, price, stock, payment and transaction state.

Flow:
1. Select product.
2. Read NFC credential.
3. POST vending transaction with an idempotency key.
4. Authorize payment on NVM server.
5. Physically dispense.
6. POST dispense result.
7. Server decrements inventory only after successful dispense.

The example firmware uses a servo and one selection button. NFC/display adapters are deliberately isolated from the transaction protocol so hardware can be changed without changing the financial flow.

Before flashing, set Wi-Fi, server address, machine ID, NFC/account mapping and actual GPIOs.
