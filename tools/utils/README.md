# schema_diff.py

Use this utility to display the list of providers, filters, and
actions that have been added or removed between two given versions.
Here's the command that writes out the differences between Custodian
version 0.9.2.0 and the latest version to a file called `diff.md`:

```
python schema_diff.py 0.9.2.0 latest --only-changes --out=diff.md
```

This assumes that `custodian-cask` is available in your environment.
If you want to display a list of all filters and actions, regardless
of whether they changes or not, omit the `--only-changes` flag.
