import requests
import bolt11


class LUD16:

    @staticmethod
    def connect(url: str):
        user, domain = url.split('@')
        url = f"https://{domain}/.well-known/lnurlp/{user}"
        ret = requests.get(url).json()
        if ret['status'] == 'OK':
            callback = ret['callback']
            metadata = ret['metadata']
            min_sendable = ret['minSendable']
            max_sendable = ret['maxSendable']
            tag = ret['tag']
            if tag != 'payRequest':
                return
            try:
                data = {
                    'callback': callback,
                    'metadata': metadata,
                    'min_sendable': min_sendable,
                    'max_sendable': max_sendable,
                    'tag': tag,
                    }
                return data
            except:
                return
        else:
            return

    @staticmethod
    def process_callback_url(data, amount) -> str:
        return LUD16.process_callback_url_msats(data, amount*1000)

    @staticmethod
    def process_callback_url_msats(data, amount) -> str:
        return f"{data['callback']}?&amount={amount}"

    @staticmethod
    def get_invoice(url: str, amount: int):
        data = LUD16.connect(url)
        if data:
            callback_url = LUD16.process_callback_url(data, amount)
            ret = requests.get(callback_url).json()
            if ret['status'] == 'OK':
                invoice = ret['pr']
                a = bolt11.decode(invoice).amount
                if a == amount*1000:
                    return invoice
                else:
                    return
            else:
                return
        else:
            return