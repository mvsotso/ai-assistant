class Reminder {
  final int id;
  final String message;
  final String? remindAt;
  final String? createdAt;
  final bool isSent;
  final int? taskId;
  final String? taskTitle;
  final String? eventId;
  final int snoozeCount;
  final bool isRecurring;
  final String? recurrenceRule;

  Reminder({
    required this.id,
    required this.message,
    this.remindAt,
    this.createdAt,
    this.isSent = false,
    this.taskId,
    this.taskTitle,
    this.eventId,
    this.snoozeCount = 0,
    this.isRecurring = false,
    this.recurrenceRule,
  });

  factory Reminder.fromJson(Map<String, dynamic> json) => Reminder(
        id: json['id'] ?? 0,
        message: json['message'] ?? json['title'] ?? '',
        remindAt: json['remind_at'],
        createdAt: json['created_at'],
        isSent: json['is_sent'] ?? false,
        taskId: json['task_id'],
        taskTitle: json['task_title'],
        eventId: json['event_id']?.toString(),
        snoozeCount: json['snooze_count'] ?? 0,
        isRecurring: json['is_recurring'] ?? false,
        recurrenceRule: json['recurrence_rule'],
      );
}
