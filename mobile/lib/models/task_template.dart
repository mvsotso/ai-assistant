class TaskTemplate {
  final int id;
  final String name;
  final String titleTemplate;
  final String? descriptionText;
  final String? icon;
  final String? color;
  final String priority;
  final String status;
  final String? category;
  final String? subcategory;
  final String? assigneeName;
  final int? dueOffsetHours;
  final int? groupId;
  final int? subgroupId;
  final List<dynamic>? checklist;
  final int useCount;

  TaskTemplate({
    required this.id,
    required this.name,
    required this.titleTemplate,
    this.descriptionText,
    this.icon,
    this.color,
    this.priority = 'medium',
    this.status = 'todo',
    this.category,
    this.subcategory,
    this.assigneeName,
    this.dueOffsetHours,
    this.groupId,
    this.subgroupId,
    this.checklist,
    this.useCount = 0,
  });

  factory TaskTemplate.fromJson(Map<String, dynamic> json) => TaskTemplate(
        id: json['id'] ?? 0,
        name: json['name'] ?? '',
        titleTemplate: json['title_template'] ?? '',
        descriptionText: json['description_text'],
        icon: json['icon'],
        color: json['color'],
        priority: json['priority'] ?? 'medium',
        status: json['status'] ?? 'todo',
        category: json['category'],
        subcategory: json['subcategory'],
        assigneeName: json['assignee_name'],
        dueOffsetHours: json['due_offset_hours'],
        groupId: json['group_id'],
        subgroupId: json['subgroup_id'],
        checklist: json['checklist'] as List?,
        useCount: json['use_count'] ?? 0,
      );
}
