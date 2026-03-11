class Task {
  final int id;
  final String title;
  final String? description;
  final String status;
  final String priority;
  final String? assignee;
  final String? category;
  final String? subcategory;
  final String? dueDate;
  final String? createdAt;
  final int? groupId;
  final String? groupName;

  Task({
    required this.id, required this.title, this.description,
    required this.status, required this.priority, this.assignee,
    this.category, this.subcategory, this.dueDate, this.createdAt,
    this.groupId, this.groupName,
  });

  factory Task.fromJson(Map<String, dynamic> json) => Task(
    id: json['id'] ?? 0,
    title: json['title'] ?? '',
    description: json['description'],
    status: json['status'] ?? 'todo',
    priority: json['priority'] ?? 'medium',
    assignee: json['assignee'] ?? json['assignee_name'],
    category: json['category'],
    subcategory: json['subcategory'],
    dueDate: json['due_date'],
    createdAt: json['created_at'],
    groupId: json['group_id'],
    groupName: json['group_name'],
  );

  Map<String, dynamic> toJson() => {
    'title': title, 'description': description, 'status': status,
    'priority': priority, 'assignee_name': assignee, 'category': category,
    'subcategory': subcategory, 'due_date': dueDate,
    if (groupId != null) 'group_id': groupId,
  };
}
