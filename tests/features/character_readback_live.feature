@e2e @e2e_character
Feature: Read back an existing Character personality through CLI and MCP
  The operator supplies the expected personality digest. Both read-only surfaces
  must return the same entity and workflow binding without changing the entity.

  Scenario: CLI and native MCP read the existing Character personality
    Given an opted-in existing Character and expected personality digest
    When the CLI reads the Character
    Then its identity and personality digest match the operator's expected state
    When native MCP stdio reads the same Character
    Then MCP identity and personality digest match the CLI read
