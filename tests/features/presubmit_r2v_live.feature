@e2e @e2e_auth
Feature: The live migrated entry point stops before generation
  Scenario: An unverified 10s R2V is refused without upload or media submit
    Given an explicitly configured owned Flow profile and project
    When the real client receives a 10s Omni reference video request
    Then it returns positive pre-submit configuration proof
    And no upload or generation request was dispatched
