import 'dart:convert';
import '../config/api_config.dart';
import 'api_service.dart';

class AIService {
  /// Build a context string from user's tasks for AI awareness.
  static Future<String> _buildTaskContext() async {
    try {
      final data = await ApiService.get(ApiConfig.tasks, params: {'limit': '50'});
      final tasks = data is List ? data : (data['tasks'] ?? []);
      if (tasks.isEmpty) return 'User has no tasks.';

      final buffer = StringBuffer();
      buffer.writeln('User\'s current tasks:');
      for (final t in tasks) {
        final title = t['title'] ?? 'Untitled';
        final status = t['status'] ?? 'unknown';
        final priority = t['priority'] ?? 'medium';
        final assignee = t['assignee_name'] ?? '';
        final due = t['due_date'] ?? '';
        buffer.writeln('- [$status] $title (priority: $priority${assignee.isNotEmpty ? ", assignee: $assignee" : ""}${due.isNotEmpty ? ", due: $due" : ""})');
      }
      return buffer.toString();
    } catch (_) {
      return '';
    }
  }

  static Future<Map<String, dynamic>> chat(String message, {List<Map<String, String>>? history}) async {
    // Fetch task context so AI knows about user's tasks
    final context = await _buildTaskContext();

    return await ApiService.post(ApiConfig.aiChat, {
      'message': message,
      'context': context,
      if (history != null) 'history': history,
    });
  }

  static Future<Map<String, dynamic>> prioritize() async {
    return await ApiService.post(ApiConfig.aiPrioritize, {'include_workload': true});
  }
}
