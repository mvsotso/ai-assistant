import 'package:flutter/material.dart';
import '../config/theme.dart';

class StatusChip extends StatelessWidget {
  final String status;
  const StatusChip({super.key, required this.status});

  Color get _color {
    switch (status) {
      case 'todo': return const Color(0xFF6B7094);
      case 'in_progress': return AppTheme.blue;
      case 'review': return AppTheme.purple;
      case 'done': return AppTheme.green;
      default: return AppTheme.muted;
    }
  }

  String get _label {
    switch (status) {
      case 'todo': return 'To Do';
      case 'in_progress': return 'In Progress';
      case 'review': return 'Review';
      case 'done': return 'Done';
      default: return status;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: _color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 6, height: 6, decoration: BoxDecoration(shape: BoxShape.circle, color: _color)),
          const SizedBox(width: 4),
          Text(_label, style: TextStyle(fontSize: 10, color: _color, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}
