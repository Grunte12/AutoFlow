@e2e @e2e_auth
Feature: An empty migrated mention picker never submits the composer
  # The mention query is typed into the live composer. Enter with no visible result
  # can hit Flow's composer submit handler; route interception keeps this browser
  # regression local and zero-credit.

  Scenario: an empty picker does not press Enter or submit
    Given a migrated composer whose mention picker has no results
    When the driver mentions the requested asset
    Then the composer was not submitted and no mention chip was added

  Scenario: a hidden stale option is not treated as an available result
    Given a migrated composer whose only stale mention option is hidden
    When the driver mentions the requested asset
    Then the composer was not submitted and no mention chip was added

  Scenario: a visible picker result commits the expected mention chip
    Given a migrated composer whose picker offers the requested asset
    When the driver mentions the requested asset
    Then the expected mention chip was committed without submitting
