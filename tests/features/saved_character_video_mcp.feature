@e2e @e2e_video
Feature: Saved Characters generate through the native MCP queue
  Scenario: One explicitly authorized Character clip has a terminal local output
    Given an explicit one-clip saved Character test request
    When the request runs once through the candidate stdio MCP server
    Then MCP reports a completed task with a local playable video
