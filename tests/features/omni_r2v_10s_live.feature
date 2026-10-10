@e2e @e2e_auth
Feature: Omni Flash 10s mixed-reference wire capture without generation
  Scenario: The registered MCP handler binds two Characters and two local images at 10s
    Given an opt-in private Omni R2V request with two Characters and two images
    When the native MCP handler captures its submit with generation blocked
    Then exactly one Omni R2V 10s submit is captured without dispatch
    And both Character and media bindings and the prompt are verified
