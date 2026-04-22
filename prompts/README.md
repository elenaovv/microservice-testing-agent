# Prompts Package

This package prepares the context sent to the agent.

Current responsibilities in `generator.py`:
- load the MSA spec text
- load the system description
- load legacy text use cases
- load structured YAML use cases and the use-case index
- derive journey-based Python test filenames
- build a focused execution brief from the selected inputs
- build the browse prompt
- build the test-generation prompt

The prompt path is MSA-agnostic. It can use different spec files and different use-case sets through CLI path overrides rather than assuming one fixed system.
