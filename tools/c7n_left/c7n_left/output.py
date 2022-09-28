from c7n.output import OutputRegistry

from rich.console import Console


report_outputs = OutputRegistry()
report_outputs.default = "rich"


@report_outputs.register("rich")
class RichCli:
    def __init__(self, ctx, config):
        self.ctx = ctx
        self.config = config
        self.console = Console()

    def report(self, results):
        pass
