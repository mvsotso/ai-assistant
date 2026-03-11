class TeamMember {
  final int id;
  final String? firstName;
  final String? lastName;
  final String fullName;
  final String? email;
  final String? department;
  final String? title;

  TeamMember({
    required this.id,
    this.firstName,
    this.lastName,
    required this.fullName,
    this.email,
    this.department,
    this.title,
  });

  factory TeamMember.fromJson(Map<String, dynamic> json) {
    final fn = json['first_name'] as String? ?? '';
    final ln = json['last_name'] as String? ?? '';
    return TeamMember(
      id: json['id'] ?? 0,
      firstName: json['first_name'],
      lastName: json['last_name'],
      fullName: json['full_name'] ?? '$fn $ln'.trim(),
      email: json['email'],
      department: json['department'],
      title: json['title'],
    );
  }
}
