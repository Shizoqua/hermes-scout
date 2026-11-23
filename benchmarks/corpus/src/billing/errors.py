"""Error codes shown to customers on the billing pages."""


class BillingError(Exception):
    code = "E4000"


class PaymentDeclined(BillingError):
    code = "E4021"


class DuplicateInvoice(BillingError):
    code = "E4090"


class CardExpired(BillingError):
    code = "E4022"
