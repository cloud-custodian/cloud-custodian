from c7n.exceptions import CustodianError


class EventNotMatchedException(CustodianError):
    """
    Event not matched
    """


class PolicyNotRunnableException(CustodianError):
    """
    Policy is not runnable
    """
