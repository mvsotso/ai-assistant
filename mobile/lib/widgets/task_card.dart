import 'package:flutter/material.dart';
import '../models/task.dart';
import '../config/theme.dart';
import 'priority_badge.dart';
import 'status_chip.dart';

class TaskCard extends StatelessWidget {
  final Task task;
  final VoidCallback? onTap;

  const TaskCard({super.key, required this.task, this.onTap});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(task.title,
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppTheme.text),
                      maxLines: 2, overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  PriorityBadge(priority: task.priority),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  StatusChip(status: task.status),
                  const SizedBox(width: 8),
                  if (task.assignee != null)
                    Expanded(
                      child: Text(task.assignee!,
                        style: const TextStyle(fontSize: 11, color: AppTheme.muted),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  if (task.dueDate != null)
                    Text(task.dueDate!.split('T').first,
                      style: const TextStyle(fontSize: 11, color: AppTheme.muted),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
