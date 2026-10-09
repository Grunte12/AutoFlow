Feature: Configuration proof is explicit, not inferred
  Scenario: A known transport refusal reaches CLI and MCP unchanged
    Given a positively witnessed duration refusal
    When the error is serialized for CLI and MCP
    Then both surfaces say the request was not submitted
    And the CLI keeps exit code 11

  Scenario: An ordinary configuration error does not permit replay
    Given an ordinary configuration error
    When the error is serialized for CLI and MCP
    Then neither surface claims a pre-submit proof
