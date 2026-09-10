import { Component, inject, signal, computed } from '@angular/core';
import { DomainService } from '../../core/services/domain';

@Component({
  selector: 'ob-status',
  standalone: true,
  templateUrl: './index.html',
  styleUrl: '../shared.css',
})
export class StatusComponent {
  private readonly domain: DomainService = inject(DomainService);

  protected readonly searchQuery = signal('');

  protected readonly filteredStatuses = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const all = this.domain.getStatuses();
    if (!q) return all;
    return all.filter(
      s => s.code.includes(q) || s.description.toLowerCase().includes(q)
    );
  });
}