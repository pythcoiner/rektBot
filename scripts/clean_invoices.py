from RPC import RPC

invoices = RPC.list_invoices()

for i in invoices:
    label = i['label']
    status = i['status']
    RPC.del_invoice(label, status)


