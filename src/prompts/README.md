# Prompts Package

This package prepares the context sent to the agent.

Main files:
- `generator.py`: compatibility facade for callers that import prompt helpers from one place.
- `use_cases.py`: legacy and structured use-case loading.
- `spec_context.py`: MSA/spec loading and focused service-slice construction.
- `builders.py`: browse and test-generation prompt assembly.
- `journey_rendering.py`: replay-plan and journey-contract rendering for prompts.
- `filenames.py`: generated-test filename derivation and validation.
- `templates/`: Markdown templates for long static prompt instructions.

The prompt path is MSA-agnostic. It can use different spec files and different use-case sets through CLI path overrides rather than assuming one fixed system.
