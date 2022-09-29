from c7n.output import OutputRegistry

from rich.console import Console


report_outputs = OutputRegistry("left")
report_outputs.default_protocol = "rich"


def get_reporter(config):
    return report_outputs.select(None, None)


@report_outputs.register("rich")
@report_outputs.register("default")
class RichCli:
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config
        self.console = Console()

    def report(self, results):
        self.console.print(results)

    def flush(self):
        pass
