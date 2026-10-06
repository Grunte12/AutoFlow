Feature: Conservative local-image video batches
  The batch runner is deterministic, credit-aware and offline-preflightable.

  Scenario: A valid dry run does not launch Chrome
    Given a video manifest containing two supplied local-image shots
    When I dry run the video batch
    Then all shots are reported as not started
    And no browser client is constructed

  Scenario: A bad later shot blocks the entire batch before Chrome
    Given a video manifest containing two supplied local-image shots
    And the later shot has an empty prompt
    When I dry run the video batch
    Then preflight rejects the manifest
    And no browser client is constructed
