@e2e @e2e_auth
Feature: Duration controls are selected by their numeric domain, not unit language
  Scenario Outline: Ten seconds is available when the unit is translated
    Given a duration row whose unit is "<unit>"
    When the shared composer selects ten seconds
    Then the ten-second radio alone is checked
    And no generation is submitted

    Examples:
      | unit      |
      | s         |
      | วินาที    |
      | 秒        |
      | Sekunden  |

  Scenario: Reference duration pin also uses the numeric control
    Given a duration row whose unit is "วินาที"
    When the shared composer pins the reference duration
    Then the eight-second radio alone is checked
    And no generation is submitted

  Scenario: Two matching duration groups cannot be guessed
    Given two complete duration rows
    When the shared composer selects ten seconds
    Then ambiguity is reported without clicking
    And no generation is submitted
