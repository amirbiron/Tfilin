# Contributing to Tefillin Bot

## Development Setup

### Prerequisites
- Python 3.11+
- MongoDB (for local testing)
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/amirbiron/Tfilin.git
cd Tfilin
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install development dependencies:
```bash
make install-dev
# Or manually:
pip install -r requirements-dev.txt
```

4. Copy environment variables:
```bash
cp .env.example .env
# Edit .env with your values
```

## Development Workflow

### Running Tests
```bash
# Run all tests with coverage
make test

# Run specific test file
pytest tests/test_database.py -v

# Run tests matching pattern
pytest -k "test_reminder" -v
```

### Code Quality

#### Linting
```bash
# Check code style
make lint

# Auto-format code
make format
```

#### Type Checking
```bash
make type-check
```

### Pre-commit Checks
Before committing, run:
```bash
make pre-commit
```

## Testing Guidelines

### Writing Tests

1. Place tests in `tests/` directory
2. Name test files as `test_*.py`
3. Use descriptive test names: `test_<feature>_<scenario>`
4. Mock external dependencies (database, API calls)
5. Test both success and failure cases

### Test Structure
```python
class TestFeature:
    @pytest.fixture
    def setup(self):
        # Setup code
        pass
    
    def test_success_case(self, setup):
        # Test implementation
        assert result == expected
    
    def test_error_case(self, setup):
        with pytest.raises(ExpectedError):
            # Code that should raise error
```

## CI/CD Pipeline

### GitHub Actions
The CI pipeline runs on:
- Every push to `main` and `develop`
- Every pull request to `main`

Pipeline stages:
1. **Linting**: Code style checks
2. **Type Checking**: Static type analysis
3. **Testing**: Unit and integration tests
4. **Security**: Vulnerability scanning
5. **Docker**: Build and test Docker image

### Local CI Run
```bash
make ci
```

## Code Style

### Python Style Guide
- Follow PEP 8
- Maximum line length: 127 characters
- Use type hints for function signatures
- Document functions with docstrings

### Commit Messages
Format:
```
<type>: <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Code style changes
- `refactor`: Code refactoring
- `test`: Test additions/changes
- `chore`: Build/tooling changes

Example:
```
feat: add reminder snooze functionality

- Add snooze button to reminder messages
- Store snooze duration in database
- Reschedule reminder after snooze

Closes #123
```

## Pull Request Process

1. Fork the repository
2. Create feature branch: `git checkout -b feature/your-feature`
3. Make changes and commit
4. Run tests: `make test`
5. Push to your fork
6. Create Pull Request

### PR Checklist
- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] Commit messages follow convention
- [ ] PR description explains changes

## Project Structure
```
Tfilin/
├── .github/
│   └── workflows/      # GitHub Actions workflows
├── tests/              # Test files
│   ├── test_database.py
│   ├── test_handlers.py
│   └── test_scheduler.py
├── main_updated.py     # Main bot file
├── database.py         # Database operations
├── handlers.py         # Command handlers
├── scheduler.py        # Reminder scheduler
├── requirements.txt    # Production dependencies
├── requirements-dev.txt # Development dependencies
├── Dockerfile         # Docker configuration
├── pytest.ini         # Pytest configuration
├── pyproject.toml     # Tool configurations
└── Makefile          # Development commands
```

## Debugging

### Running Bot Locally
```bash
# Set environment variables
export TELEGRAM_BOT_TOKEN="your_token"
export MONGODB_URI="mongodb://localhost:27017/tefillin"
export ADMIN_ID="your_telegram_id"

# Run bot
python main_updated.py
```

### MongoDB Local Setup
```bash
# Using Docker
docker run -d -p 27017:27017 --name mongodb mongo:latest

# Connect to MongoDB
mongosh mongodb://localhost:27017/tefillin
```

## Getting Help

- Open an issue for bugs/features
- Join our Telegram group: [link]
- Email: support@tefillinbot.com

## License

This project is licensed under the MIT License.