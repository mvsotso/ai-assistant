class Category {
  final int id;
  final String name;
  final String? icon;
  final String? color;
  final List<Subcategory> subcategories;
  final int taskCount;

  Category({
    required this.id,
    required this.name,
    this.icon,
    this.color,
    this.subcategories = const [],
    this.taskCount = 0,
  });

  factory Category.fromJson(Map<String, dynamic> json) => Category(
        id: json['id'] ?? 0,
        name: json['name'] ?? '',
        icon: json['icon'],
        color: json['color'],
        subcategories: (json['subcategories'] as List?)
                ?.map((s) => Subcategory.fromJson(s))
                .toList() ??
            [],
        taskCount: json['task_count'] ?? 0,
      );
}

class Subcategory {
  final int id;
  final String name;
  final int taskCount;

  Subcategory({required this.id, required this.name, this.taskCount = 0});

  factory Subcategory.fromJson(Map<String, dynamic> json) => Subcategory(
        id: json['id'] ?? 0,
        name: json['name'] ?? '',
        taskCount: json['task_count'] ?? 0,
      );
}
