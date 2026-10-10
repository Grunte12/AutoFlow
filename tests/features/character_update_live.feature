@e2e @e2e_character
Feature: Update existing Character images without creating or generating entities
  The update uses only an operator-selected existing Character and local source images.
  Every replay is read-only and must preserve the operation journal.

  Scenario: MCP updates both slots and CLI and MCP replays do not mutate again
    Given an opted-in existing Character and portrait and full-body source images
    When MCP stdio updates both Character image slots
    Then both returned slots match the sources and the journal is verified
    When the CLI replays the same Character update operation
    Then the CLI replay matches and the journal is unchanged
    When MCP stdio replays the same Character update operation
    Then the MCP replay matches and the journal is unchanged

  Scenario: CLI updates portrait only and MCP replay preserves the full-body slot
    Given an opted-in existing Character and portrait and full-body source images
    When the CLI updates only the portrait slot
    Then the journal proves the omitted slot and metadata were preserved
    When MCP stdio replays the same Character update operation
    Then the MCP replay matches and the journal is unchanged
