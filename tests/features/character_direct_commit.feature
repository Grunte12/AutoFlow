@e2e @e2e_auth
Feature: Character rows commit directly to the prompt
  Scenario: Exact named character options are committed without a second confirmation
    Given a browser composer with an existing media chip and exact character options
    When I select the requested characters through the composer
    Then the requested entity IDs are attached in order and the media chip is preserved
    And no Enter key or Add button is used

  Scenario Outline: A direct commit with the wrong identity is refused
    Given a browser composer with a direct <commit> commit
    When I validate the requested character entity
    Then the composer raises ReferenceNotFoundError before submission

    Examples:
      | commit             |
      | a different entity |
      | a media chip       |
