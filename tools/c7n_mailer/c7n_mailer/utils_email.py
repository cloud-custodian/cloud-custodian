import logging
from email.utils import parseaddr

logger = logging.getLogger('c7n_mailer.utils.email')


def is_email(target):
    if target is None:
        return False
    if target.startswith('slack://'):
        logger.debug("Slack payload, not an email.")
        return False
    if parseaddr(target)[1] and '@' in target and '.' in target:
        return True
    else:
        return False
