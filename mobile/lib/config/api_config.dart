/// API configuration for the AI Personal Assistant backend.
class ApiConfig {
  static const String baseUrl = 'https://aia.rikreay24.com/api/v1';

  // Auth
  static const String authVerify = '$baseUrl/auth/google/verify';
  static const String authSession = '$baseUrl/auth/verify';
  static const String authClientId = '$baseUrl/auth/client-id';

  // Tasks
  static const String tasks = '$baseUrl/tasks';
  static String taskById(int id) => '$baseUrl/tasks/$id';
  static const String board = '$baseUrl/board';
  static const String dashboard = '$baseUrl/dashboard';

  // Task Actions / Checklist
  static String taskActions(int taskId) => '$baseUrl/tasks/$taskId/actions';
  static String taskActionById(int taskId, int actionId) =>
      '$baseUrl/tasks/$taskId/actions/$actionId';
  static String taskActionToggle(int taskId, int actionId) =>
      '$baseUrl/tasks/$taskId/actions/$actionId/toggle';

  // AI
  static const String aiChat = '$baseUrl/ai/chat';
  static const String aiPrioritize = '$baseUrl/ai/prioritize';
  static const String aiSuggestTime = '$baseUrl/ai/suggest-time';

  // Calendar
  static const String calendarEvents = '$baseUrl/calendar/events';

  // Reminders
  static const String reminders = '$baseUrl/reminders';
  static const String reminderHistory = '$baseUrl/reminders/history';
  static String reminderById(int id) => '$baseUrl/reminders/$id';
  static String reminderSnooze(int id) => '$baseUrl/reminders/$id/snooze';

  // Team
  static const String team = '$baseUrl/team-mgmt/members';

  // Categories
  static const String categories = '$baseUrl/categories';

  // Task Groups
  static const String taskGroups = '$baseUrl/task-groups';

  // Templates
  static const String templates = '$baseUrl/templates';
  static String templateUse(int id) => '$baseUrl/templates/$id/use';

  // Notifications
  static const String notifCount = '$baseUrl/notifications/count';
}
