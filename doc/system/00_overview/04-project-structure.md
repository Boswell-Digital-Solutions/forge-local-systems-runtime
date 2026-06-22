## 4. Project Structure

### 4.1 Directory Layout

```text
forge-local-runtime/
├── .mypy_cache/
├── .vscode/
├── DECISIONS/
├── db/
├── doc/
├── docs/
├── runtime_promotion/
├── schemas/
├── scripts/
├── tests/
```

### 4.2 Documentation Rule

- `doc/system/` is the canonical modular source for the root `SYSTEM.md`
- `scripts/context-bundle.sh` is the selective context assembly surface
- `CLAUDE.md` is the repo-local AI instruction file
