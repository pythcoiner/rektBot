import os
from typing import Union
import logging

from peewee import *

from PySide6.QtCore import QObject, Signal

log = logging.getLogger()


class Order(Model):
    order_id = CharField(unique=True)
    deposit_id = CharField()
    user = CharField()
    order_type = CharField()
    mode = CharField()
    amount = IntegerField()
    leverage = IntegerField()

    status = CharField()
    profit = IntegerField()  # unpaid paid funding funded open close
    invoice = CharField()
    lnm_id = CharField()
    tp = IntegerField(null=True)
    open_price = FloatField(null=True)
    close_price = FloatField(null=True)

    class Meta:
        database = None


class OrderManager(QObject):
    order_status_updated = Signal(object)
    order_status_new = Signal(object)
    order_status_unpaid = Signal(object)
    order_status_paid = Signal(object)
    order_status_expired = Signal(object)
    order_status_funding = Signal(object)
    order_status_funding_fail = Signal(object)
    order_status_funded = Signal(object)
    order_status_open = Signal(object)
    order_status_close = Signal(object)
    order_status_deleted = Signal(object)

    def __init__(self, db_path='bot.sqlite'):
        QObject.__init__(self)

        self.db = SqliteDatabase(db_path)
        Order._meta.database = self.db

        if os.path.exists(db_path):
            self.db.connect()
        else:
            self.db.connect()
            self.db.create_tables([Order], safe=True)

    def get_order_by_id(self, order_id) -> Union[Order | None]:
        log.log(15, f"get_order_by_id({order_id=})")
        try:
            return Order.get(Order.order_id == order_id)
        except Order.DoesNotExist:
            return None

    def get_order_status(self, order_id) -> Union[str | None]:
        order = self.get_order_by_id(order_id)
        if order:
            return str(order.status)
        else:
            return None

    def list_unpaid_orders(self):
        return Order.select().where(Order.status == 'unpaid')

    def list_funding_orders(self):
        return Order.select().where(Order.status == 'funding')

    def list_open_orders(self):
        return Order.select().where(Order.status == 'open')

    def new_order(self, data):
        log.log(15, f"new_order({data=})")
        order = Order(order_id=data['order_id'],
                      deposit_id='',
                      user=data['user'],
                      amount=data['amount'],
                      order_type=data['order_type'],
                      status='new',
                      profit=0,
                      invoice='',
                      lnm_id='',
                      tp=data['tp'],
                      leverage=data['leverage'],
                      open_price=0,
                      close_price=0,
                      mode=data['mode'],
                      )
        order.save()
        self.order_status_new.emit(order)
        self.order_status_updated.emit(order)

    def set_order_unpaid(self, data):
        log.log(15, f"set_order_unpaid({data=})")
        order_id = data['order_id']
        invoice = data['invoice']
        order = self.get_order_by_id(order_id)
        order.invoice = invoice
        order.status = 'unpaid'
        if 'hash' in data.keys():
            order.deposit_id = data['hash']
        order.save()
        self.order_status_unpaid.emit(order)
        self.order_status_updated.emit(order)

    def set_order_paid(self, order_id):
        log.log(15, f"set_order_paid({order_id=})")
        order = self.get_order_by_id(order_id)
        order.status = 'paid'
        order.save()
        self.order_status_paid.emit(order)
        self.order_status_updated.emit(order)

    def set_order_expired(self, order_id):
        log.log(15, f"set_order_expired({order_id=})")
        order = self.get_order_by_id(order_id)
        order.status = 'expired'
        order.save()
        self.order_status_expired.emit(order)
        self.order_status_updated.emit(order)

    def set_order_funding(self, order_id):
        log.log(15, f"set_order_funding({order_id=})")
        order = self.get_order_by_id(order_id)
        order.status = 'funding'
        order.save()
        self.order_status_funding.emit(order)
        self.order_status_updated.emit(order)

    def set_order_funded(self, order_id):
        log.log(15, f"set_order_funded({order_id=})")
        order = self.get_order_by_id(order_id)
        order.status = 'funded'
        order.save()
        self.order_status_funded.emit(order)
        self.order_status_updated.emit(order)
        
    def set_order_funding_fail(self, order_id):
        log.log(15, f"set_order_funding_fail({order_id=})")
        order = self.get_order_by_id(order_id)
        order.status = 'funding_fail'
        order.save()
        self.order_status_funding_fail.emit(order)
        self.order_status_updated.emit(order)

    def set_order_open(self, data):
        log.log(15, f"set_order_open({data=})")
        order_id = data['order_id']
        price = data['price']
        lnm_id = data['lnm_id']
        order = self.get_order_by_id(order_id)
        order.status = 'open'
        order.open_price = price
        order.lnm_id = lnm_id
        order.save()
        self.order_status_open.emit(order)
        self.order_status_updated.emit(order)

    def set_order_close(self, data):
        log.log(15, f"set_order_close({data=})")
        order_id = data['order_id']
        price = data['price']
        order = self.get_order_by_id(order_id)
        order.status = 'close'
        order.close_price = price
        # TODO: Calculate Profit
        # TODO: Send back money
        order.save()
        self.order_status_close.emit(order)
        self.order_status_updated.emit(order)

    def del_order(self, order_id) -> bool:
        try:
            order = Order.get(Order.id == order_id)
            order.delete_instance()
            self.order_status_deleted.emit(order)
            self.order_status_updated.emit(order)
            return True
        except Order.DoesNotExist:
            return False

    def close(self):
        self.db.close()