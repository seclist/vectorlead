# 🤝 Contributing to VectorLead

Thank you for your interest in contributing to **VectorLead**! We welcome bug fixes, algorithmic improvements, new modular niche definitions, and documentation enhancements.

---

## 🛠 Local Development Setup

### 1. Prerequisites
- Python 3.11 or higher
- Git

### 2. Fork & Clone
```bash
git clone https://github.com/your-username/vectorlead.git
cd vectorlead
```

### 3. Virtual Environment
```bash
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate

# On Windows PowerShell:
.venv\Scripts\Activate.ps1
```

### 4. Install Dependencies
Install VectorLead in editable development mode with testing tools:
```bash
pip install -e .[dev]
```

---

## 📐 Project Structure

```
vectorlead/
├── config/
│   └── niches.yaml         # Pluggable niche keywords and exclusion rules
├── src/
│   ├── algorithm.py        # AHS momentum math, EQS, FMI, churn filters
│   ├── scraper.py          # Zero-login crawler verification via OpenGraph
│   ├── classifier.py       # Modular NLP niche evaluator
│   ├── database.py         # SQLite local cache and history
│   └── sheets_sync.py      # Non-destructive Google Sheets & CSV CRM engine
├── tests/                  # Pytest test suite
└── main.py                 # Rich CLI entry point
```

---

## 🧪 Testing Guidelines

We enforce **zero regressions** and high test coverage. Every new feature or fix must include unit tests.

```bash
# Run pytest test suite
pytest -v

# Run with full coverage report
pytest --cov=src --cov-report=term-missing tests/
```

---

## 🎨 Code Quality Standards

VectorLead uses `ruff` for linting and formatting:

```bash
# Check code style
ruff check .

# Auto-fix formatting issues
ruff check --fix .
```

Rules to remember:
- Keep type annotations on all function signatures (`src/`).
- Avoid adding heavy third-party dependencies unless strictly necessary.
- Respect rate-limiting and zero-login crawler constraints. Never add invasive scraping methods requiring credentials or session cookies.

---

## 🚀 Submitting a Pull Request

1. Create a descriptive branch:
   ```bash
   git checkout -b feat/add-chiropractor-niche
   ```
2. Commit with conventional commit messages (`feat:`, `fix:`, `docs:`, `test:`).
3. Push to your fork:
   ```bash
   git push origin feat/add-chiropractor-niche
   ```
4. Open a Pull Request on GitHub and fill out the provided template.

Thank you for building VectorLead with us! 🚀
