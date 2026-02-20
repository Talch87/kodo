# KODO 2.0 Deployment Guide

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Talch87/kodo.git
cd kodo

# Install dependencies
pip install -r requirements.txt

# Or use uv (faster)
uv sync
```

### Basic Usage

```python
from kodo.orchestrator import Kodo2Orchestrator
import asyncio

async def main():
    orchestrator = Kodo2Orchestrator()
    
    # Process code through full autonomous pipeline
    result = await orchestrator.process_code(
        code="def add(a, b): return a + b",
        code_id="feature_001",
        test_code="assert add(1, 2) == 3",
    )
    
    # Check decision
    if result.auto_action == "deploy":
        print("✅ Code ready for production!")
    elif result.auto_action == "review":
        print("👀 Code ready for review")
    else:
        print("❌ Code needs fixes")

asyncio.run(main())
```

### CLI Usage

```bash
# Process code file through full pipeline
python -m kodo.main process mycode.py --test test_mycode.py

# Verify code only
python -m kodo.main verify mycode.py

# Generate report
python -m kodo.main report feature_123

# Show help
python -m kodo.main --help
```

## Verification Checklist

Before deploying KODO 2.0, verify all components:

### Code Compilation ✅
```bash
# Verify all imports work
python -c "
from kodo.verification import VerificationEngine
from kodo.quality import QualityGate
from kodo.production import ComplianceValidator, ProductionReadinessScorer
from kodo.reliability import FailureHealer
from kodo.transparency import AuditTrail, DecisionType
from kodo.cost import TokenTracker, ModelType
from kodo.learning import FeedbackCollector, TrustScorer, AutomatedImprovement
from kodo.orchestrator import Kodo2Orchestrator
print('✅ All imports successful!')
"
```

### Test Suite ✅
```bash
# Run all tests
pytest tests/test_kodo_2_0.py -v
pytest tests/test_kodo_2_0_extended.py -v

# Run with coverage
pytest tests/ --cov=kodo --cov-report=html
```

### Documentation ✅
```bash
# Verify documentation files exist
ls -lh KODO_2_0_README.md
ls -lh KODO_2_0_ARCHITECTURE.md
ls -lh KODO_2_0_COMPLETE.md
ls -lh KODO_2_0_DEPLOYMENT.md
```

### Code Statistics ✅
```bash
# Count lines of code
wc -l kodo/**/*.py tests/test_*.py

# Expected: 5000+ lines
```

## Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY kodo/ ./kodo/

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "kodo.api:app", "--host", "0.0.0.0"]
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kodo-2-0
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kodo-2-0
  template:
    metadata:
      labels:
        app: kodo-2-0
    spec:
      containers:
      - name: kodo
        image: kodo:latest
        ports:
        - containerPort: 8000
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### Monitoring & Observability

```bash
# Prometheus metrics endpoint
GET /metrics

# Health check
GET /health

# Logs
docker logs -f kodo-container
```

## Integration with CI/CD

### GitHub Actions

```yaml
name: KODO 2.0 Verification

on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: pip install pytest pytest-asyncio pytest-cov
      
      - name: Run tests
        run: pytest tests/ -v --cov=kodo
      
      - name: Verify imports
        run: python -c "from kodo.orchestrator import Kodo2Orchestrator; print('✓ All imports OK')"
```

### GitLab CI

```yaml
test:
  stage: test
  image: python:3.10
  script:
    - pip install pytest pytest-asyncio pytest-cov
    - pytest tests/ -v --cov=kodo
    - python -c "from kodo.orchestrator import Kodo2Orchestrator; print('✓ OK')"
```

## Configuration

### Environment Variables

```bash
# API Configuration
export KODO_API_PORT=8000
export KODO_API_HOST=0.0.0.0

# Model Selection
export KODO_DEFAULT_MODEL=claude-haiku
export KODO_VERIFY_MODEL=claude-haiku
export KODO_GENERATE_MODEL=claude-sonnet

# Thresholds
export KODO_MIN_VERIFICATION_SCORE=90
export KODO_MIN_TRUST_SCORE=70

# Logging
export KODO_LOG_LEVEL=INFO
export KODO_LOG_FILE=/var/log/kodo.log
```

### Configuration File (kodo.yaml)

```yaml
verification:
  min_pass_score: 90
  timeout_seconds: 30

quality_gate:
  auto_merge_threshold: 1.0
  enable_security_check: true

production:
  min_compliance: 1.0
  readiness_thresholds:
    production: 90
    staging: 75
    dev: 60

cost:
  track_tokens: true
  warn_threshold_usd: 100.0
  track_models:
    - claude-haiku
    - claude-sonnet
    - gpt-4

feedback:
  collect_enabled: true
  analysis_frequency: daily

trust:
  weights:
    verification: 0.40
    quality: 0.30
    feedback: 0.20
    consistency: 0.10
  min_trust_to_deploy: 85

logging:
  level: INFO
  format: json
  output: stdout
```

## Performance Tuning

### Optimization Tips

1. **Parallel Execution**
   - Run independent verification tests in parallel
   - Use async/await throughout

2. **Caching**
   - Cache verification results for identical code
   - Cache quality gate results per component

3. **Model Selection**
   - Use Claude Haiku for fast verification
   - Use Claude Sonnet for complex analysis
   - Use Claude Opus only when needed

4. **Cost Optimization**
   - Batch similar requests
   - Use prompt caching for repeated specs
   - Monitor model pricing changes

### Expected Performance

```
Operation                 Time        Cost
─────────────────────────────────────────
Verification (5 tests)    ~2-5s       $0.02
Quality Gate (7 checks)   ~1-3s       $0.01
Compliance Check          ~1s         $0.005
Production Readiness      ~1s         $0.005
Trust Calculation         <1s         <$0.001
Full Pipeline             ~5-10s      $0.05
```

## Troubleshooting

### Common Issues

**Issue: "ImportError: cannot import name 'ModelType'"**
```bash
Solution: Ensure all __init__.py files are updated with proper exports
python -c "from kodo.cost import ModelType"
```

**Issue: "Test failures in test_kodo_2_0.py"**
```bash
Solution: Ensure pytest-asyncio is installed
pip install pytest-asyncio
```

**Issue: "Cost calculation not working"**
```bash
Solution: Verify MODEL_PRICING dict is in kodo/cost/tracker.py
grep -n "MODEL_PRICING" kodo/cost/tracker.py
```

### Debug Mode

```python
# Enable detailed logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable orchestrator debugging
from kodo.orchestrator import Kodo2Orchestrator
orchestrator = Kodo2Orchestrator()

# Set trace on all pillars
orchestrator.verifier.verbose = True
orchestrator.quality.verbose = True
# ... etc
```

## Maintenance

### Regular Tasks

```bash
# Weekly: Run full test suite
pytest tests/ -v

# Monthly: Update cost models
python -m kodo.cost.update_pricing

# Quarterly: Analyze patterns and improve
python -m kodo.learning.generate_improvements

# Yearly: Performance audit
python -m kodo.cli report-performance
```

### Backup & Recovery

```bash
# Backup audit trail
cp -r audit_trail_db/ audit_trail_db.backup.$(date +%Y%m%d)

# Restore from backup
cp -r audit_trail_db.backup.20250220/ audit_trail_db/

# Export all decision history
python -m kodo.cli export-decisions decisions.json
```

## Security Considerations

### API Security

```python
# Enable authentication
from kodo.api import create_app
app = create_app(
    require_auth=True,
    auth_secret="your-secret-key"
)

# Enable rate limiting
from slowapi import Limiter
limiter = Limiter(key_func=lambda: "global")
@limiter.limit("100/minute")
async def process(request):
    ...

# Enable request validation
from pydantic import BaseModel, validator
class CodeRequest(BaseModel):
    code: str
    test_code: Optional[str]
    
    @validator('code')
    def code_not_empty(cls, v):
        if not v.strip():
            raise ValueError('Code cannot be empty')
        return v
```

### Audit Trail Security

```bash
# Sign audit trail records
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem

# Enable encryption
export KODO_ENCRYPT_AUDIT_TRAIL=true
export KODO_ENCRYPTION_KEY=$(cat encryption_key.txt)
```

## Scaling Considerations

### Horizontal Scaling

- Deploy multiple instances behind load balancer
- Use shared database for audit trail
- Implement distributed caching
- Use message queue for async jobs

### Vertical Scaling

- Allocate more CPU for parallel processing
- Increase memory for large code analysis
- Optimize database queries
- Use connection pooling

## Health Checks

```python
async def health_check():
    """Full system health check"""
    checks = {
        "verification": await verify_engine_status(),
        "quality": await quality_gate_status(),
        "database": await database_status(),
        "api": await api_status(),
    }
    
    all_healthy = all(checks.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    }
```

## Support & Feedback

- 📋 Documentation: See KODO_2_0_README.md
- 🏗️ Architecture: See KODO_2_0_ARCHITECTURE.md
- 📦 Complete Info: See KODO_2_0_COMPLETE.md
- 🐛 Issues: github.com/Talch87/kodo/issues
- 💬 Discussions: github.com/Talch87/kodo/discussions

## Version Compatibility

- Python: 3.10+
- Tested on: Ubuntu 20.04+, macOS 11+, Windows 10+
- Dependencies: See requirements.txt
- Latest: v2.0.0

## License

KODO 2.0 is part of the Kodo project. See LICENSE file for details.
