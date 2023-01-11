"""Build an arn-type database from aws iam reference docs

Inspired by duo-labs/parliament and salesforce/policy_sentry which
also parse the reference docs.

The simplest way to run is actually checkout policy_sentry since
it has a clean copy of the html data.

```
gh repo clone salesforce/policy_sentry
python arnref.py --docs-dir policy-sentry/shared/data/docs --output arn-types.json
```

"""
from pathlib import Path
import json

import click
from bs4 import BeautifulSoup

from c7n.resources.aws import Arn


def extract_arns(service_page):
    soup = BeautifulSoup(service_page.read_text(), "html.parser")
    main_content = soup.find(id="main-content")
    if main_content is None:
        return

    tables = main_content.find_all("div", class_="table-contents")

    arn_map = {}
    for t in tables:
        if not header_matches("resource types", t) or not header_matches("arn", t):
            continue
        rows = t.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) == 0:
                # skip header row
                continue
            if len(cells) != 3:
                raise ValueError("unexpected resource cell count")
            resource = cells[0].text.strip()
            arn = "".join(cells[1].text.split()).replace("$", "")
            arn_map[resource] = arn
    return arn_map


def header_matches(string, table):
    headers = [str(x).lower() for x in table.find_all("th")]
    found = False
    for header in headers:
        if string in header:
            found = True
            break
    return found


@click.command()
@click.option("--docs-dir", type=click.Path())
@click.option("--output", type=click.File("wb"), default="-")
def main(docs_dir, output):
    docs_dir = Path(docs_dir)

    arn_db = {}
    for page in sorted(docs_dir.glob("*.html")):
        service_page = docs_dir / page
        if "rds" in service_page.name:
            import pdb

            pdb.set_trace()
        service_arns = extract_arns(service_page)
        if not service_arns:
            continue
        sample = next(iter(service_arns.values()))
        service_key = Arn.parse(sample).service

        arn_db.setdefault(service_key, {}).update(service_arns)

    output.write(json.dumps(arn_db, indent=2).encode("utf8"))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import pdb, sys, traceback

        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
