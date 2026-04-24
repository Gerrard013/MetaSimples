document.addEventListener('DOMContentLoaded', () => {
    const flashes = document.querySelectorAll('.flash');

    if (flashes.length) {
        setTimeout(() => {
            flashes.forEach((item) => {
                item.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
                item.style.opacity = '0';
                item.style.transform = 'translateY(-4px)';

                setTimeout(() => {
                    item.remove();
                }, 360);
            });
        }, 5000);
    }

    const useCommissionInput = document.getElementById('use_commission');
    const commissionField = document.getElementById('commissionField');
    const commissionInput = commissionField ? commissionField.querySelector('input') : null;

    const syncCommissionState = () => {
        if (!useCommissionInput || !commissionField || !commissionInput) return;

        const enabled = useCommissionInput.checked;
        commissionField.classList.toggle('is-disabled', !enabled);
        commissionInput.disabled = !enabled;

        if (!enabled) {
            commissionInput.value = '';
        }
    };

    if (useCommissionInput) {
        syncCommissionState();
        useCommissionInput.addEventListener('change', syncCommissionState);
    }

    const repeatedDigitsRegex = /^(\d)\1+$/;
    const normalizeWhatsapp = (value) => value.replace(/\D/g, '').replace(/^55(?=\d{11}$)/, '');

    const formatWhatsapp = (value) => {
        const digits = normalizeWhatsapp(value).slice(0, 11);
        if (digits.length <= 2) return digits;
        if (digits.length <= 7) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
        return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7, 11)}`;
    };

    const isValidWhatsapp = (value) => {
        const digits = normalizeWhatsapp(value);
        if (digits.length !== 11) return false;
        const ddd = Number(digits.slice(0, 2));
        return ddd >= 11 && ddd <= 99 && digits[2] === '9' && !repeatedDigitsRegex.test(digits);
    };

    document.querySelectorAll('[data-whatsapp-check="true"]').forEach((input) => {
        input.addEventListener('input', () => {
            input.value = formatWhatsapp(input.value);
        });
    });

    document.querySelectorAll('[data-validate-form]').forEach((form) => {
        form.addEventListener('submit', () => {
            const button = form.querySelector('button[type="submit"]');
            const whatsappInput = form.querySelector('[data-whatsapp-check="true"]');

            if (whatsappInput && !isValidWhatsapp(whatsappInput.value)) {
                alert('Informe um WhatsApp válido com DDD e 9 dígitos.');
                return;
            }

            if (button) {
                button.disabled = true;
                button.innerText = 'Enviando...';
            }
        });
    });
});