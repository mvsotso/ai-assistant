class TaskGroup {
  final int id;
  final String name;
  final String? icon;
  final String? color;
  final List<TaskSubGroup> subgroups;
  final int taskCount;

  TaskGroup({
    required this.id,
    required this.name,
    this.icon,
    this.color,
    this.subgroups = const [],
    this.taskCount = 0,
  });

  factory TaskGroup.fromJson(Map<String, dynamic> json) => TaskGroup(
        id: json['id'] ?? 0,
        name: json['name'] ?? '',
        icon: json['icon'],
        color: json['color'],
        subgroups: (json['subgroups'] as List?)
                ?.map((s) => TaskSubGroup.fromJson(s))
                .toList() ??
            [],
        taskCount: json['task_count'] ?? 0,
      );
}

class TaskSubGroup {
  final int id;
  final String name;
  final int taskCount;

  TaskSubGroup({required this.id, required this.name, this.taskCount = 0});

  factory TaskSubGroup.fromJson(Map<String, dynamic> json) => TaskSubGroup(
        id: json['id'] ?? 0,
        name: json['name'] ?? '',
        taskCount: json['task_count'] ?? 0,
      );
}
