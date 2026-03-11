class Reminder {
  final int id;
  final String title;
  final String? remindAt;
  final bool isCompleted;
  final int? taskId;

  Reminder({required this.id, required this.title, this.remindAt, this.isCompleted = false, this.taskId});

  factory Reminder.fromJson(Map<String, dynamic> json) => Reminder(
    id: json['id'] ?? 0,
    title: json['title'] ?? '',
    remindAt: json['remind_at'],
    isCompleted: json['is_completed'] ?? false,
    taskId: json['task_id'],
  );
}
