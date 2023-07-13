import subprocess
import json
import logging

log = logging.getLogger()


class RPC:

    @staticmethod
    def to_json(txt):
        return json.loads(txt)

    @staticmethod
    def rpc_call(command: str, param=None):
        if param is not None:
            param = ' '.join(param)
        else:
            param = ''

        command = f"/usr/bin/lightning-cli {command} {param}"
        # print(command)
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.stderr:
            log.log(15, f"rpc_call fail with {command=}: {result.stderr=}")
            return RPC.to_json(result.stderr)
        else:
            return RPC.to_json(result.stdout)

    @staticmethod
    def pay_invoice(bolt11) -> bool:
        log.info(f"[Core Lightning RPC] try to pay Invoice")
        log.log(15,f"[Core Lightning RPC] Invoice: {bolt11}")
        out = RPC.rpc_call('pay', [bolt11])

        if out['status'] == 'complete':
            log.info(f"[Core Lightning RPC] Invoice paid")
            return True
        else:
            log.info(f"[Core Lightning RPC] Fail to pay Invoice")
            log.log(15,f"[Core Lightning RPC] {out}")
            return False


    @staticmethod
    def invoice(amount: int, label: str, expiry=600):
        if type(amount) == str:
            amount = int(amount)

        if type(expiry) == int:
            expiry = str(expiry)

        log.info(f"[Core Lightning RPC] Invoice")
        log.log(15,f"Invoice: {amount=}, {label=}, {expiry=}")
        out = RPC.rpc_call(command="invoice", param=[str(amount * 1000), label
            , f"'rektBot: play with {amount} sats and you will be likely rekt!'", expiry])

        if type(out) == list:
            print(out)
        else:
            # print(f"{out=}")
            return out['bolt11']

    @staticmethod
    def invoice_status(label) -> str:
        invoices = RPC.list_invoices()
        for i in invoices:
            if i['label'] == label:
                log.debug(f"Status: {i['status']}")
                return i['status']
        log.debug(f"Status: invoice_not_exist")
        return 'invoice_not_exist'

    @staticmethod
    def list_invoices():
        return RPC.rpc_call('listinvoices')['invoices']

    @staticmethod
    def del_invoice(label, status):
        log.info(f"[Core Lightning RPC] Delete invoice {label[:5]}_{label[-5:]}")
        return RPC.rpc_call('delinvoice', [label, status])

    @staticmethod
    def del_all_invoices():
        log.info(f"[Core Lightning RPC] Delete all invoices")
        invoices = RPC.list_invoices()

        for i in invoices['invoices']:
            label = i['label']
            status = i['status']
            RPC.del_invoice(label, status)
            
    @staticmethod
    def del_expired_invoices():
        log.info(f"[Core Lightning RPC] Delete expired invoices")
        return RPC.rpc_call('delexpiredinvoice')



