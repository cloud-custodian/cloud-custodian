class SplunkHecDelivery(object):

    def __init__(self, config, session, logger):
        self.config = config
        self.logger = logger
        self.session = session

    def get_splunk_events(self, sqs_message):
        raise NotImplementedError("WIP")
        return []

    def send_splunk_messages(self, messages, sqs_message):
        raise NotImplementedError("WIP")
