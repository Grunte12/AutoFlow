@e2e @e2e_auth
Feature: macOS generation runs without taking over the desktop
  Scenario: Owned background pages remain minimized through browser work and polling
    Given a disposable headed Chrome profile on macOS
    When generation opens two background pages
    And a page fills a prompt uploads a local fixture and clicks a settings control
    And the video status observer encounters a stall
    Then the original desktop application retains focus
    And both browser windows remain minimized
    And browser interactions and timer polling still work
