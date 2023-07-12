from dataclasses import dataclass

@dataclass()
class Order:
    id: str = ''
    user: str = ''
    type: str = ''
    amount: int = 0
    status: str = ''
    profit: int = 0
    invoice: str = ''
    lnm_id: str = ''

    @staticmethod
    def from_string(txt):
        order = Order()
        if txt[-1] == '\n':
            txt = txt[:-1]
        data = txt.split(':')
        if len(data) != 8:
            raise ValueError(f'data len might be 8 but is {len(data)}!')
        order.id = data[0]
        order.user = data[1]
        order.type = data[2]
        order.amount = int(data[3])
        order.status = data[4]
        order.profit = int(data[5])
        order.invoice = data[6]
        order.lnm_id = data[7]
        return order

    def to_string(self) -> str:
        return f"{self.id}:{self.user}:{self.type}:{self.amount}:{self.status}:{self.profit}:{self.invoice}:{self.lnm_id}\n"



