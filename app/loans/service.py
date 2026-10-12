from uuid import uuid4
class LoanService:
    def __init__(self,db): self.db=db
    def create(self,member_id,principal,installment_amount):
        if principal<=0 or installment_amount<=0: raise ValueError("principal and installment_amount must be positive")
        loan_id="loan-"+uuid4().hex
        with self.db.connect() as c:
            c.execute("INSERT INTO loan_accounts(loan_id,member_id,principal,installment_amount,status,remaining_balance) VALUES(?,?,?,?,?,?)",(loan_id,member_id,principal,installment_amount,"pending",principal)); c.commit()
        return {"loan_id":loan_id,"status":"pending","remaining_balance":principal}
