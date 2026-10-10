Feature: Profile-local project reuse
  Scenario: Omitted project uses the selected project
    Given an existing project is bound to this profile
    When a generation omits the project
    Then the selected project is reused

  Scenario: Corrupted binding never creates a scratch project
    Given the profile binding is corrupted
    When a generation omits the project
    Then routing fails before project creation
