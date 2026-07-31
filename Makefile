.PHONY: doctor validate agent review buzz-preflight buzz-e2e build-buzz-tools

doctor:
	./city2 doctor

validate:
	./city2 validate

agent:
	@test -n "$(PROMPT)" || (echo 'Usage: make agent PROMPT="..."' >&2; exit 2)
	./city2 agent "$(PROMPT)"

review:
	./city2 review

buzz-preflight:
	./city2 buzz preflight

buzz-e2e:
	./city2 buzz e2e

build-buzz-tools:
	./scripts/build-buzz-tools.sh
