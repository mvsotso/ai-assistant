/// API configuration for the AI Personal Assistant backend.
class ApiConfig {
  static const String baseUrl = 'https://aia.rikreay24.com/api/v1';

  static const String authVerify = '$baseUrl/auth/google/verify';
  static const String authSession = '$baseUrl/auth/verify';
  static const String authClientId = '$baseUrl/auth/client-id';

  static const String tasks = '$baseUrl/tasks';
  static String taskById(int id) => '$baseUrl/tasks/$id';
  static const String board = '$baseUrl/board';
  static const String dashboard = '$baseUrl/dashboard';

  static const String aiChat = '$baseUrl/ai/chat';
  static const String aiPrioritize = '$baseUrl/ai/prioritize';

  static const String calendarEvents = '$baseUrl/calendar/events';
  static const String reminders = '$baseUrl/reminders';
  static const String team = '$baseUrl/team-mgmt/members';
  static const String categories = '$baseUrl/categories';
  static const String notifCount = '$baseUrl/notifications/count';
}
