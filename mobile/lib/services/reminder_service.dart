import 'package:flutter/foundation.dart';
import '../config/api_config.dart';
import '../models/reminder.dart';
import 'api_service.dart';

class ReminderService {
  static Future<List<Reminder>> getReminders() async {
    debugPrint('[Reminders] Fetching pending reminders from ${ApiConfig.reminders}');
    final data = await ApiService.get(ApiConfig.reminders);
    debugPrint('[Reminders] Response keys: ${data.keys.toList()}');
    debugPrint('[Reminders] Raw data: $data');
    return (data['reminders'] as List?)
            ?.map((r) => Reminder.fromJson(r))
            .toList() ??
        [];
  }

  static Future<List<Reminder>> getHistory({int limit = 50}) async {
    final data = await ApiService.get(ApiConfig.reminderHistory,
        params: {'limit': '$limit'});
    return (data['reminders'] as List?)
            ?.map((r) => Reminder.fromJson(r))
            .toList() ??
        [];
  }

  static Future<Map<String, dynamic>> create(Map<String, dynamic> body) async {
    return await ApiService.post(ApiConfig.reminders, body);
  }

  static Future<Map<String, dynamic>> snooze(int id, int minutes) async {
    return await ApiService.patch(
        ApiConfig.reminderSnooze(id), {'minutes': minutes});
  }

  static Future<void> delete(int id) async {
    await ApiService.delete(ApiConfig.reminderById(id));
  }
}
