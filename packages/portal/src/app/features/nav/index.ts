import { Component, inject, signal, computed } from '@angular/core';
import { DomainService } from '../../core/services/domain';

@Component({
  selector: 'ob-nav',
  standalone: true,
  templateUrl: './index.html',
  styleUrl: '../shared.css',
})
export class NavComponent {
  private readonly domain: DomainService = inject(DomainService);
  protected readonly searchQuery = signal('');
  protected readonly selectedOp = signal<string | null>(null);

  protected readonly filteredOps = computed(() => {
    const q = this.searchQuery().trim();
    return q ? this.domain.searchOperations(q) : this.domain.getOperations();
  });
}
