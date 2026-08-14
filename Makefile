.PHONY: test lint syntax source-gates audit package

test:
	python3 -m unittest discover -s tests -v

lint:
	python3 scripts/validate_contracts.py

syntax:
	python3 scripts/host_syntax_check.py

source-gates:
	python3 scripts/source_gates.py

audit:
	python3 scripts/final_audit.py

package: audit
	python3 scripts/make_release.py
