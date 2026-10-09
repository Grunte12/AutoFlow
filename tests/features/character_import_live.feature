@e2e @e2e_character
Feature: Original Character sheets import through CLI and MCP stdio
  The opt-in run creates uniquely named verification Characters from the supplied
  sheet. It does not edit canonical Goofy or Memo Characters and never generates media.

  Scenario: CLI and MCP imports replay the same exact native bindings
    Given an opted-in Flow profile, project, and source image
    When the real CLI imports a uniquely named verification Character
    And the CLI replays the first Character with its same operation UUID
    Then the CLI import and replay return the same exact entity and bindings
    And the CLI Character retains its name and personality after reload
    When the real MCP stdio server imports a separate verification Character
    And the MCP stdio server replays it with the same operation UUID
    Then the MCP import and replay return the same exact entity and bindings
    And the MCP Character retains its name and personality after reload
    And the isolated journal contains only these two import operations

  Scenario: MCP import replays read-only through both CLI and MCP stdio
    Given the final opted-in Flow profile, project, and source image
    When MCP stdio imports one final verification Character
    And the CLI replays it with the same operation UUID
    And MCP stdio replays it again with the same operation UUID
    Then the MCP import and CLI/MCP replays return the same exact entity and bindings
    And the final MCP Character retains its name and personality after reload
    And the final journal contains only one completed import operation
