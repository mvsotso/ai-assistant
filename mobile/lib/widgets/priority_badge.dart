import 'package:flutter/material.dart';
import '../config/theme.dart';

class PriorityBadge extends StatelessWidget {
  final String priority;
  const PriorityBadge({super.key, required this.priority});

  Color get _color {
    switch (priority) {
      case 'urgent': return AppTheme.red;
      case 'high': return AppTheme.orange;
      case 'medium': return AppTheme.blue;
      case 'low': return AppTheme.muted;
      default: return AppTheme.blue;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: _color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(priority.toUpperCase(),
        style: TextStyle(fontSize: 10, fontWeight: FontWeight.w600, color: _color),
      ),
    );
  }
}
