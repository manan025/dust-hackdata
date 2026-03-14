#!/usr/bin/env bash

set -euo pipefail

WORKDIR="${1:-/work}"
OUTDIR="${OUTDIR:-/out}"
PERF_LOOPS="${PERF_LOOPS:-3}"

cd "$WORKDIR"
export PYTHONPATH="/runner:${PYTHONPATH:-}"

main_lang="$(python3 - <<'PY'
import os
from collections import Counter

base = os.getcwd()
skip_dirs = {
    ".git", "node_modules", "vendor", "dist", "build", "target", ".venv", "venv",
    "__pycache__", ".idea", ".vscode",
}

ext_map = {
    ".go": "go",
    ".py": "python",
    ".js": "node",
    ".jsx": "node",
    ".ts": "node",
    ".tsx": "node",
    ".rs": "rust",
    ".java": "java",
    ".cs": "dotnet",
    ".rb": "ruby",
    ".php": "php",
}

counts = Counter()
for root, dirs, files in os.walk(base):
    dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
    for name in files:
        _, ext = os.path.splitext(name)
        lang = ext_map.get(ext.lower())
        if lang:
            counts[lang] += 1

weights = Counter()
if os.path.isfile("go.mod"):
    weights["go"] += 1000
if os.path.isfile("package.json"):
    weights["node"] += 1000
if os.path.isfile("pyproject.toml") or os.path.isfile("requirements.txt") or os.path.isfile("setup.py"):
    weights["python"] += 1000
if os.path.isfile("Cargo.toml"):
    weights["rust"] += 1000
if os.path.isfile("pom.xml") or os.path.isfile("build.gradle") or os.path.isfile("build.gradle.kts"):
    weights["java"] += 1000
if any(name.endswith(".csproj") for name in os.listdir(".")):
    weights["dotnet"] += 1000
if os.path.isfile("Gemfile"):
    weights["ruby"] += 1000
if os.path.isfile("composer.json"):
    weights["php"] += 1000

if not counts and not weights:
    print("unknown")
else:
    combined = counts + weights
    print(combined.most_common(1)[0][0])
PY
)"

test_cmd=""
run_cmd=""

case "$main_lang" in
  go)
    test_cmd="go test ./..."
    run_cmd="go run ."
    ;;
  node)
    npm install
    if node -e "const pkg=require('./package.json'); process.exit(pkg.scripts && pkg.scripts.test ? 0 : 1)"; then
      test_cmd="npm test"
    fi
    if node -e "const pkg=require('./package.json'); process.exit(pkg.scripts && pkg.scripts.start ? 0 : 1)"; then
      run_cmd="npm run start"
    elif [ -f index.js ]; then
      run_cmd="node index.js"
    elif [ -f app.js ]; then
      run_cmd="node app.js"
    fi
    ;;
  python)
    if [ -f requirements.txt ]; then
      python3 -m pip install -r requirements.txt
    elif [ -f pyproject.toml ]; then
      python3 -m pip install .
    fi
    if find . -maxdepth 2 -type d -name tests | grep -q . || find . -maxdepth 2 -type f -name "test_*.py" | grep -q .; then
      python3 -m pip install pytest
      test_cmd="python3 -m pytest"
    fi
    if [ -f main.py ]; then
      run_cmd="python3 main.py"
    elif [ -f app.py ]; then
      run_cmd="python3 app.py"
    elif [ -f run.py ]; then
      run_cmd="python3 run.py"
    fi
    ;;
  rust)
    test_cmd="cargo test"
    run_cmd="cargo run --release"
    ;;
  java)
    if [ -f mvnw ]; then
      chmod +x mvnw
      test_cmd="./mvnw test"
      run_cmd="./mvnw -q -DskipTests package && java -jar \$(ls target/*.jar | head -n 1)"
    elif [ -f pom.xml ]; then
      test_cmd="mvn test"
      run_cmd="mvn -q -DskipTests package && java -jar \$(ls target/*.jar | head -n 1)"
    elif [ -f gradlew ]; then
      chmod +x gradlew
      test_cmd="./gradlew test"
      run_cmd="./gradlew run"
    elif [ -f build.gradle ] || [ -f build.gradle.kts ]; then
      test_cmd="gradle test"
      run_cmd="gradle run"
    fi
    ;;
  dotnet)
    test_cmd="dotnet test"
    run_cmd="dotnet run"
    ;;
  ruby)
    if [ -f Gemfile ]; then
      gem install bundler
      bundle install
      if [ -f Rakefile ]; then
        test_cmd="bundle exec rake test"
      fi
    fi
    if [ -f main.rb ]; then
      run_cmd="ruby main.rb"
    fi
    ;;
  php)
    if [ -f composer.json ]; then
      composer install --no-interaction
      if [ -x vendor/bin/phpunit ]; then
        test_cmd="vendor/bin/phpunit"
      fi
    fi
    if [ -f index.php ]; then
      run_cmd="php index.php"
    fi
    ;;
  *)
    echo "Unable to detect main language." >&2
    exit 1
    ;;
esac

if [ -n "$test_cmd" ]; then
  echo "Running tests: $test_cmd"
  bash -lc "$test_cmd"
fi

if [ -z "$run_cmd" ]; then
  echo "No runnable entrypoint found for $main_lang." >&2
  exit 2
fi

echo "Profiling command with perf-agent: $run_cmd"
python3 -m perf_agent.cli \
  --command "$run_cmd" \
  --loops "$PERF_LOOPS" \
  --out-dir "$OUTDIR"

cat > "$OUTDIR/metadata.json" <<EOF
{"language":"$main_lang","test_cmd":"$test_cmd","run_cmd":"$run_cmd","perf_loops":$PERF_LOOPS}
EOF
