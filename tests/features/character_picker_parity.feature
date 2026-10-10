@e2e @e2e_auth
Feature: Existing Character reference picker parity
  Compare the native picker with the production composer using only existing project assets.

  Scenario: Native and production composer produce equivalent guarded R2V input
    Given an opted-in migrated project with existing media and saved Characters
    When the native picker and production composer inputs are captured with submit blocked
    Then ordered reference bindings match and backend image consumption remains unproved
