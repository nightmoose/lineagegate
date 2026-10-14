PY ?= .venv/bin/python
LG ?= .venv/bin/lineagegate

.PHONY: venv up seed demo test
venv:
	python3 -m venv .venv && .venv/bin/pip install -e '.[llm,dev]'
up:
	docker compose up -d
seed:
	$(LG) seed
demo:
	$(LG) ask --show-tools "What breaks if stg_orders.amount changes from dollars to cents?"
test:
	.venv/bin/pytest -q
