# Example

Create a directory, snapshot it, change a file, create another snapshot, then compare them:

```powershell
fileledger snapshot . .\before.json
fileledger snapshot . .\after.json
fileledger diff .\before.json .\after.json
fileledger verify . .\before.json
```

`diff` and `verify` return exit code `1` when differences are found.
# Example workflow

```powershell
fileledger snapshot . baseline.json --exclude .git --exclude build
fileledger verify . baseline.json --exclude .git --exclude build
fileledger verify . baseline.json --exclude .git --exclude build --format text
fileledger diff baseline.json later.json --format text
```

Use the same repeated `--exclude` values when creating and verifying a snapshot.
